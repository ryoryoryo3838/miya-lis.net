[@react.component]
let make = () => {
  <>
    <h1> {R.s @@ "This is /miya-lis.net/"} </h1>
    <h2> {R.s @@ "Created with ReasonReact + Melange + Vite!!!"} </h2>
    <h3>
      <a href="https://astro.miya-lis.net/">
        {R.s @@ {j|旧サイトはこちら|j}}
      </a>
    </h3>
    <DirListing />
  </>;
};
