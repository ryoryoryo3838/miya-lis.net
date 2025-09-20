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
    <div>
      <p className="text-5xl m-5">
        {R.s @@
         "これは Miya がセルフホストしてるウェブサイトです。"}
      </p>
      <ul className="m-5 ml-8">
        {Util.showList(contentsList, ~cN="text-5xl m-5 link-hover")}
      </ul>
      <div className="text-3xl m-5 ml-8 text-gray-500">
        {R.s @@ "デザインは気が向いたらなんとかします"}
      </div>
    </div>
  </>;
};
