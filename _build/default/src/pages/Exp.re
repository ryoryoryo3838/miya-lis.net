let contentsList = [
  ("/aboutme", "じぶん"),
  ("/link", "りんく"),
  ("/aqualium", "さかな"),
  ("/misc", "いろいろ"),
];
let showList = lst => {
  lst
  |> List.map(((path, name)) =>
       <li className="text-5xl m-5 link-hover">
         <a href=path> {R.s @@ name} </a>
       </li>
     )
  |> Array.of_list
  |> React.array;
};
[@react.component]
let make = () => {
  <>
    <header>
      <h1 className="text-8xl m-5"> {R.s @@ "Miya-lis.net/"} </h1>
    </header>
    // タイトル部分、ルーティングに合わせて末尾にpathを足していきたい
    <div>
      <p className="text-5xl m-8">
        {R.s @@
         "これは Miya がセルフホストしてるウェブサイトです。"}
      </p>
      <ul className="m-5 ml-8">
        //<li className="text-5xl m-5 link-hover"><a href="/aboutme"> {R.s @@ "じぶん"} </a></li>
        //<li className="text-5xl m-5"> {R.s @@ "りんく"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "きろく"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "さかな"} </li>
        //<li className="text-5xl m-5"> {R.s @@ "いろいろ"} </li>
         {showList(contentsList)} </ul>
      <div className="text-3xl m-5 ml-8 text-gray-500">
        {R.s @@ "デザインは気が向いたらなんとかします"}
      </div>
    </div>
  </>;
};
