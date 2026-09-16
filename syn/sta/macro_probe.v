// macro_probe.v -- REG8x16 のタイミング制約を OpenSTA が本当に見るかを
// 確かめるためだけの最小ネットリスト。設計とは無関係。
//
// ★ 「Liberty が読める」と「OpenSTA がその制約を使う」は別（U7）。
//   REG8x16 はクロックを持たないマクロなので、hold_rising や
//   min_pulse_width が黙って無視される可能性がある。ここで確かめる。
//
// 構成: DFF が ADD / D / WEB を駆動し、REG8x16 がそれを受ける。
//       WEB にクロックを当てれば min_pulse_width の対象になる。
module macro_probe (input CK, input DIN, output [7:0] QOUT);
  wire [3:0] a;
  wire [7:0] d;
  wire       web;

  DFF u_a0 (.CK(CK), .D(DIN),  .Q(a[0]), .QB());
  DFF u_a1 (.CK(CK), .D(a[0]), .Q(a[1]), .QB());
  DFF u_a2 (.CK(CK), .D(a[1]), .Q(a[2]), .QB());
  DFF u_a3 (.CK(CK), .D(a[2]), .Q(a[3]), .QB());
  DFF u_w  (.CK(CK), .D(a[3]), .Q(web),  .QB());
  DFF u_d0 (.CK(CK), .D(DIN),  .Q(d[0]), .QB());
  DFF u_d1 (.CK(CK), .D(d[0]), .Q(d[1]), .QB());
  DFF u_d2 (.CK(CK), .D(d[1]), .Q(d[2]), .QB());
  DFF u_d3 (.CK(CK), .D(d[2]), .Q(d[3]), .QB());
  DFF u_d4 (.CK(CK), .D(d[3]), .Q(d[4]), .QB());
  DFF u_d5 (.CK(CK), .D(d[4]), .Q(d[5]), .QB());
  DFF u_d6 (.CK(CK), .D(d[5]), .Q(d[6]), .QB());
  DFF u_d7 (.CK(CK), .D(d[6]), .Q(d[7]), .QB());

  REG8x16 u_mem (.ADD(a), .D(d), .WEB(web), .Q(QOUT));
endmodule
