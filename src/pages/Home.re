let contentsList = [
  ("/aboutme", "じぶん"),
  ("/link", "りんく"),
  ("/bookshelf", "ほんだな"),
  ("/aqualium", "さかな"),
  ("/misc", "いろいろ"),
];
[@react.component]
let make = () => {
  <>
    // タイトル部分、ルーティングに合わせて末尾にpathを足していきたい
    <div>
      <p className="text-5xl m-5">
        {R.s @@
         "これは Miya がセルフホストしてるウェブサイトです。"}
      </p>
      <ul className="m-5 ml-8">
        //<li className="text-5xl m-5 link-hover"><a href="/aboutme"> {R.s @@ "じぶん"} </a></li>
        //<li className="text-5xl m-5"> {R.s @@ "りんく"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "きろく"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "さかな"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "いろいろ"} </li>
         {Util.showList(contentsList, ~cN="text-5xl m-5 link-hover")} </ul>
      <div className="text-3xl m-5 ml-8 text-gray-500">
        {R.s @@ "デザインは気が向いたらなんとかします"}
      </div>
    </div>
  </>;
};
