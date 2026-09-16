# check_macro_arcs.tcl -- REG8x16 の書込み制約を OpenSTA が見るかの確認。
#
#   sta -no_splash -exit syn/sta/check_macro_arcs.tcl
#
# ★ 「Liberty が読める」と「制約が使われる」は別（U7）。read_liberty が
#   無言で通っても、hold_rising / min_pulse_width は黙って捨てられている
#   可能性がある。**出力に現れるかどうか**で判定する。
#
# ★ **2 通り試す。** hold と min_pulse_width はクロック絡みの検査なので、
#   `WEB` をただの信号として扱うか、クロックとして宣言するかで結果が変わる。
#   どちらで効くのかを確かめないと、設計側に何を要求すべきか決められない。

set here [file dirname [file normalize [info script]]]
set lib  [expr {[info exists env(LIB)] ? $env(LIB) : \
                "$here/../../stdcell/v59_4/tr1um_typ_5v0_25c.lib"}]
set net  [expr {[info exists env(NET)] ? $env(NET) : "$here/macro_probe.v"}]

proc try {label body} {
    puts "\n-- $label"
    if {[catch {uplevel 1 $body} err]} { puts "   (使えなかった: $err)" }
}

puts "== liberty : $lib"
puts "== netlist : $net"
read_liberty $lib
read_verilog $net
link_design macro_probe

create_clock -name CK -period 100 [get_ports CK]
set_input_delay  1.0 -clock CK [get_ports DIN]
set_output_delay 1.0 -clock CK [get_ports QOUT*]

puts "\n===== A. WEB を「ただの信号」として扱う ====="
try "REG8x16 が読めているか" {
    foreach c [get_lib_cells */REG8x16] { puts "   [get_name $c]" }
}
try "ADD -> Q のアーク" {
    set_input_delay 1.0 -clock CK [get_ports WEBP]
    report_checks -through [get_pins u_mem/ADD*] -path_delay max -digits 3 -endpoint_count 1
}
try "WEB -> Q のアーク" {
    report_checks -through [get_pins u_mem/WEB] -path_delay max -digits 3 -endpoint_count 1
}
try "最小パルス幅" { report_check_types -min_pulse_width -digits 3 }
try "マクロに向かう hold" {
    report_checks -to [get_pins u_mem/*] -path_delay min -digits 3 -endpoint_count 4
}

puts "\n===== B. WEB を「クロック」として宣言する ====="
try "WEB にクロックを当てる" {
    create_clock -name WEBCK -period 100 [get_ports WEBP]
}
try "最小パルス幅" { report_check_types -min_pulse_width -digits 3 }
try "マクロに向かう hold" {
    report_checks -to [get_pins u_mem/*] -path_delay min -digits 3 -endpoint_count 4
}
try "全部の検査の内訳" { report_check_types -max_delay -min_delay -digits 3 }
