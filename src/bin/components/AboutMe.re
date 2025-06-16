[@react.component]
let home = () => {
  <div
    id="title"
    className="font-serif flex flex-row justify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold items-center lg:pr-[50vw]">
    <div className="flex-col pr-0">
      <h3 className="text-3xl"> {R.s @@ "Name: miya"} </h3>
      <h3 className="text-3xl"> {R.s @@ "Affiliation: KLiS'23"} </h3>
      <h3 className="text-2xl">
        <Link path="/aboutme">
          {R.s @@ "(for more detail, see \"About me\")"}
        </Link>
      </h3>
    </div>
    <img src="/icon.svg" alt="icon" className="ml-0 w-[150px]" />
  </div>;
};

[@react.component]
let detail = () => {
  <div
    className="font-serif jstify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold">
    <h2 className="text-5xl"> {R.s @@ "About me"} </h2>
    <h3 className="text-3xl"> {R.s @@ "氏名: 清宮亮太郎"} </h3>
    <h3 className="text-3xl">
      <p> {R.s @@ "所属: "} </p>
      <ul className="pl-15">
        <li> {R.s @@ "筑波大学"} </li>
        <li> {R.s @@ "情報学群"} </li>
        <li> {R.s @@ "知識情報・図書館学類"} </li>
        <li> {R.s @@ "知識科学主専攻"} </li>
        <li> {R.s @@ "横山研究室"} </li>
      </ul>
    </h3>
  </div>;
};

[@react.component]
let element = (~category, ~lst) => {
  <>
    <p> {R.s @@ category} </p>
    <ul className="pl-15">
      {lst
       |> List.map(x => <li> {R.s @@ x} </li>)
       |> Array.of_list
       |> React.array}
    </ul>
  </>;
};
