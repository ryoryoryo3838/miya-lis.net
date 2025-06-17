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
    <h3 className="text-2xl">
      {element(
         ~category="所属: ",
         ~lst=[
           "筑波大学",
           "情報学群",
           "知識情報・図書館学類",
           "知識科学主専攻",
           "横山研究室",
           "",
         ],
       )}
      {element(
         ~category="分野: ",
         ~lst=[
           "#専攻",
           "図書館情報学(全体の理論や情報概念について)",
           "哲学(LIS-PhilとPI周辺)",
           "#興味遍歴",
           "分析哲学",
           "情報思想",
           "システム論",
           "強化学習",
           "etc...",
         ],
       )}
      {element(
         ~category="言語: ",
         ~lst=["日本語: 母語", "英語: CEFR B1程度"],
       )}
      {element(
         ~category="プログラミング言語: ",
         ~lst=[
           "#ちょっとわかる:",
           "Python",
           "OCaml",
           "Reason",
           "Elm",
           "#気になる:",
           "HTML/CSS",
           "TypeScript",
           "C",
         ],
       )}
    </h3>
  </div>;
};
