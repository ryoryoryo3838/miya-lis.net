import React, { useEffect } from "react";
import p5 from 'p5'


let t = 0; // time
const w = 700; // canvas width
const h = 700; // height

// main
const squid = (p) => {
  // init
  p.setup = () => {
    // キャンバスを作成
    p.createCanvas(w, h);
    p.clear()
  };

  // draw (時間経過ごとに再描画される)
  p.draw = () => {
    // 1. 時間変数の更新
    // なぜ円周率を入れてるのかは謎
    t += p.PI / 60;

    // 2. 背景再描画(残像上書きのため)
    p.background(255, 10);
    p.clear()
    
    // 3. 描画設定
    p.stroke(0, 100); // 線の色 (白に近い)
    p.strokeWeight(1.25); // 点を描くため線の太さを1に

    // 4. 描画ループ (10,000回)
    for (let i = 10000; i--;) {
      let y = i / 345;
      
      // -- 元のコードの a(...) 関数のロジックを展開 --
      
      // 1. 変数 k の計算
      let k;
      if (y < 11) {
        // p.pow(y, 8) は p5.js の pow()
        k = 6 + p.sin(p.pow(y, 8)) * 6;
      } else {
        k = y / 5 + p.cos(y / 2);
      }
      
      // ※注意: 元のコードの a=(...)*cos(i-t/4) の中の `i` は未定義変数です。
      // 前回の回答と同様に、ここでは仮に定数 10 として扱います (p5の定数 p.TAU/p.PIなども考えられます)。
      // const nonLoopI = 10; 
      k *= p.cos(i - t / 4);
      
      // 2. 変数 e の計算
      let e = y / 7 - 13;
      
      // 3. 距離 d の計算 (mag(k, e) に相当)
      // p.dist(x1, y1, x2, y2) は距離を計算する
      // d = mag(k, e) + sin(e/4 + t) / 2
      let d = p.dist(0, 0, k, e) + p.sin(e / 4 + t) / 2;
      
      // 4. point()関数の座標 (x, y) の計算
      
      // 変数 q の計算
      let q = y * k / d * (3 + p.sin(d * 2 + y / 2 - t * 4));
      
      // 変数 c の計算
      let c = d / 2 + 1 - t / 2;
      
      // 最終的な描画座標
      let px = q + 60 * p.cos(c) + 200;
      let py = q * p.sin(c) + d * 29 - 170;
      
      // 5. 描画
      p.point(px, py);
    }
  };
};

// p5.jsのスケッチコンポーネント
const Squid = () => {
  useEffect(() => {
    new p5(squid); // p5.jsのキャンバスを生成
  }, []);

  return React.null;
};

export default Squid;

