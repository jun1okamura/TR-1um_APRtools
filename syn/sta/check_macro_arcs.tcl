# check_macro_arcs.tcl -- REG8x16 の書込み制約を OpenSTA が見るかの確認。
#
#   sta -no_splash -exit -f syn/sta/check_macro_arcs.tcl
#   （LIB / NET は環境変数で差し替えられる）
#
# ★ 「Liberty が読める」と「制約が使われる」は別（U7）。read_liberty が
#   無言で通っても、クロックの無いマクロの hold_rising / min_pulse_width は
#   黙って捨てられている可能性がある。**出力に現れるかどうか**で判定する。

set here [file dirname [file normalize [info script]]]
set lib  [expr {[info exists env(LIB)] ? $env(LIB) : \
                "$here/../../stdcell/v59_4/tr1um_typ_5v0_25c.lib"}]
set net  [expr {[info exists env(NET)] ? $env(NET) : "$here/macro_probe.v"}]

puts "== liberty : $lib"
puts "== netlist : $net"
read_liberty $lib
read_verilog $net
link_design macro_probe

create_clock -name CK -period 100 [get_ports CK]
set_input_delay  1.0 -clock CK [get_ports DIN]
set_output_delay 1.0 -clock CK [get_ports QOUT*]

puts "\n== 1. REG8x16 が読めているか"
if {[catch {puts "cells: [get_lib_cells */REG8x16]"} e]} { puts "   ($e)" }

# ★ **1 つ落ちても残りを出す**（決定 23。OpenSTA の版で使えない旗が
#   あっても、そこで全部止まると何も分からない）
proc try {label body} {
    puts "\n== $label"
    if {[catch {uplevel 1 $body} err]} { puts "   (このコマンドは使えなかった: $err)" }
}

try "2. 読出しアーク（ADD -> Q）が使われるか" {
    report_checks -to [get_ports QOUT*] -path_delay max -digits 3
}
try "3. 制約の種類ごと（hold が出るか）" {
    report_check_types -max_delay -min_delay -digits 3
}
try "4. 最小パルス幅" {
    report_check_types -min_pulse_width -digits 3
}
try "5. マクロに向かう hold" {
    report_checks -to [get_pins u_mem/*] -path_delay min -digits 3
}
