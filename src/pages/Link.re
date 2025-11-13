let mutalList: Util.table = [
  ("https://かすしゅく.みんな", "かすしゅく"),
  ("https://zkm-web.pages.dev", "ずきも"),
  ("https://ろまのふ.かすしゅく.みんな", "ろまのふ"),
  ("https://うつぎ.かすしゅく.みんな", "うつぎ"),
];

let katteList: Util.table = [];

[@react.component]
let make = () => {
  <>
    {Util.title("りんくです")}
    <h2 className="mt-15 text-4xl m-5"> {R.s @@ "相互の人たち"} </h2>
    <ul> {Util.showList(mutalList, ~cN="text-3xl ml-10 m-5 link-hover")} </ul>
    <h2 className="mt-15 text-4xl m-5">
      {R.s @@ "勝手に見てます（敬称略）"}
    </h2>
    <ul className="text-3xl ml-10 m-5 link-hover">
      {R.s @@ "随時追加予定"}
    </ul>
  </>;
};
