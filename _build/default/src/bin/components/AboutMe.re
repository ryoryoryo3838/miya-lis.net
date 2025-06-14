[@react.component]
let home = () => {
  <div
    className="font-serif flex flex-col justify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold">
    //<h2 className="text-5xl"> {R.s @@ "About me"} </h2>

      <h3 className="text-3xl"> {R.s @@ {j|Name: miya|j}} </h3>
      <h3 className="text-3xl"> {R.s @@ {j|Affiliation: KLiS'23|j}} </h3>
      <h3 className="text-3xl">
        <Link path="/aboutme"> {R.s @@ "More detail, see Aboutme"} </Link>
      </h3>
    </div>;
};
[@react.component]
let detail = () => {
  <div
    className="font-serif jstify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold">
    <h2 className="text-5xl"> {R.s @@ "About me"} </h2>
    <h3 className="text-3xl"> {R.s @@ {j|氏名: 清宮 亮太郎|j}} </h3>
    <h3 className="text-3xl">
      <p> {R.s @@ {j|所属: |j}} </p>
      <ul className="pl-15">
        <li> {R.s @@ {j|筑波大学|j}} </li>
        <li> {R.s @@ {j|情報学群|j}} </li>
        <li> {R.s @@ {j|知識情報・図書館学類|j}} </li>
        <li> {R.s @@ {j|知識科学主専攻|j}} </li>
        <li> {R.s @@ {j|横山研究室|j}} </li>
      </ul>
    </h3>
  </div>;
};
