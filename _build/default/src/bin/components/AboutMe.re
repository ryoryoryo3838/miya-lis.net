[@react.component]
let home = () => {
  <div
    id="title"
    className="font-serif flex flex-row justify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold items-center lg:pr-[50vw]">
    <div className="flex-col pr-0">
      <h3 className="text-3xl"> {R.s @@ {j|Name: miya|j}} </h3>
      <h3 className="text-3xl"> {R.s @@ {j|Affiliation: KLiS'23|j}} </h3>
      <h3 className="text-2xl">
        <Link path="/aboutme">
          {R.s @@ "(for more detail, see \"About me\")"}
        </Link>
      </h3>
    </div>
    <img src="public/icon.svg" alt="icon" className="ml-0 w-[150px]" />
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
