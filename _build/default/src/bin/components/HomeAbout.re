[@react.component]
let make = () => {
  <div
    className="font-serif flex flex-wrap items-center justify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold">
    <h2 className="text-6xl"> {R.s @@ "About me"} </h2>
    <br />
    <h3 className="text-5xl">
      {R.s @@ {j|氏名: 清宮 亮太郎 / Ryotaro Seimiya|j}}
    </h3>
    <h3 className="text-3xl">
      {R.s @@
       {j|所属: 筑波大学 情報学群 知識情報・図書館学類 知識科学主専攻 横山研究室 |j}}
    </h3>
    <h3 className="text-3xl">
      <Link path="/aboutme"> {R.s @@ "More detail, see here..."} </Link>
    </h3>
  </div>;
};
