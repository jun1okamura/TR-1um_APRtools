# マクロ（`REG8x16` のような `is_macro_cell`）の制約を、**この設計の上で**
# STA が実際に見ているかを確かめる。`sta.sh` が `STA_MACRO_INSTS` を
# 読んで、報告の後ろに連結する（空なら連結しない）。
#
# ★ **U73 で分かっていること**（OpenSTA 3.1.0・最小ネットリスト `macro_probe.v`）:
#
#     ADD->Q / WEB->Q の組合せアーク  常に見る
#     hold_rising（ADD / D の保持）   **`WEB` がクロックのときだけ**見る
#     min_pulse_width（WEB 低。値は `.lib` から引く） **見ない**（`set_min_pulse_width` も効かない）
#
#   最小ネットリストでは `WEB` を外部ポートにしたので、クロックとして
#   宣言しない限り「パス無し」だった。**実設計では `WEB` が
#   クロックから作られていることがある**（TD4 は `OR2(clk, ~wr)`）ので、
#   その場合は**宣言しなくても伝播してくる**はず。それをここで見る。
#
# ★ 「出なかった」は「違反が無い」かもしれないし「検査していない」かも
#   しれない。**区別が付く形で出す** — hold は検査の行そのもの
#   （`library hold time`）が出るかで見る。

proc mtry {label body} {
    puts "\n  -- $label"
    if {[catch {uplevel 1 $body} err]} { puts "     (使えなかった: $err)" }
}

foreach _m $MACROS {
    puts "\n######## マクロ $_m"
    if {![llength [get_cells -quiet $_m]]} {
        puts "  ** インスタンス $_m がネットリストに無い（config.py の STA_MACRO_INSTS）"
        continue
    }
    mtry "セルの種類" {
        puts "     [get_property [get_cells $_m] ref_name]"
    }
    mtry "定義されているクロック（WEB がここに出れば伝播している）" {
        foreach c [all_clocks] {
            puts [format "     %-10s period %g" [get_name $c] [get_property $c period]]
        }
    }
    mtry "マクロへ向かう hold の一覧（`library hold time` が出れば hold_rising が効いている）" {
        # ★ **本数を絞らない。** 4 本に絞っていたら `D[0..3]` しか出ず、
        #   同じ制約が付いている `ADD` 側が見えなかった（2026-09-16）。
        #   `ADD` は書込みのたびに `ld_addr + 1` で動くので、そちらの方が効く。
        report_checks -to [get_pins $_m/*] -path_delay min -digits 3 \
                      -endpoint_path_count 24 -format summary
    }
    mtry "hold が破れているものだけ（詳細）" {
        report_checks -to [get_pins $_m/*] -path_delay min -digits 3 \
                      -endpoint_path_count 24 -slack_max 0
    }
    mtry "マクロを通る最長パス（読出し ADD -> Q が critical に乗っているか）" {
        report_checks -through [get_pins $_m/Q*] -path_delay max -digits 3 -endpoint_path_count 1
    }
    mtry "マクロへ向かう最長パス（書込み側 ADD / D / WEB の setup）" {
        report_checks -to [get_pins $_m/*] -path_delay max -digits 3 -endpoint_path_count 1
    }
    mtry "最小パルス幅（U73 より **何も出ないのが既知の正**）" {
        report_check_types -min_pulse_width -digits 3
        puts "     ★ ここが空なのは違反が無いからではなく、**OpenSTA が見ていない**から。"
        # ★ **値は `.lib` から引く**（U99）。以前は `11 ns` と直書きで、U96 で
        #   実測が 10.0 ns になったときに**写した側だけが古いまま**になった。
        #   `$MPW` は sta.sh が {セル ピン 値} で入れる（config が指定した設計だけ）。
        if {[llength $MPW] == 3 && [lindex $MPW 2] ne ""} {
            puts "        `[lindex $MPW 1]` の最小低パルス幅 [lindex $MPW 2] ns（配線容量なし、\
[lindex $MPW 0] の .lib の拘束）は ngspice 側で担保する。"
        } else {
            puts "        担保は ngspice 側（値は .lib の min_pulse_width を見ること）。"
        }
    }
}
