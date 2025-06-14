[@react.component]
let make = () => {
  <div className="font-serif">
    <Header />
    <AboutMe.home />
    //<h2> {R.s @@ "Created with ReasonReact + Melange + Vite!!!"} </h2>
    <h3 className="text-4xl pb-5 font-black">
      <a href="https://astro.miya-lis.net/">
        {R.s @@ {j|→→→旧サイトはこちら←←←|j}}
      </a>
    </h3>
    <h1 className="text-4xl">
      {R.s @@ {j|※※※ THIS WEB SITE IS UNDER CONSTRUCTION ※※※|j}}
    </h1>
    <h2 className="text-3xl">
      <Link path="/dev">
        {R.s @@ {j|→→作り途中のやつ←←|j}}
      </Link>
    </h2>
  </div>;
};

[@react.component]
let dev = () => {
  <Layout.wrap>

      <Header />
      <Layout.wrapMain> <div> <Title /> </div> </Layout.wrapMain>
    </Layout.wrap>;
    // <Table/>
};
