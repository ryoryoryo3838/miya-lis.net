[@react.component]
let make = () => {
  <>
    <h1> {R.s @@ "This is /miya-lis.net/"} </h1>
    <h2> {R.s @@ "Created with ReasonReact + Melange + VitE"} </h2>
    <h3>
      {R.s @@ {js|日本語はエラー出るんだっけなたしか|js}}
    </h3>
    <DirListing />
  </>;
};
