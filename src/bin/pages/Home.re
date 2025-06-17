let table = () => {
  <Table
    thead={
      <Table.thead 
        index=["Name", "Last modified", "Size"] 
      />}
    tbody={
      <Table.tbody
        lst = [
          ("/aboutme",["","About me","2025-06-17","-"]),
          ("/prev", ["", "Prev site", "2025-06-17", "-"]),
          ("/mutual",["", "Mutual link", "2025-06-17","-"])
        ]
      />}
  />
};


// ホーム
[@react.component]
let make = () => {
  <>
    <Layout.wrap>
      <Header />
      <Layout.wrapMain> <AboutMe.home /> {table()} </Layout.wrapMain>
    </Layout.wrap>
    <Footer />
    </>;
};

// 旧ホーム
[@react.component]
let prev = () => {
  <div className="font-serif">
    <Header />
    <AboutMe.home />
    <h3 className="text-4xl pb-5 font-black">
      <a href="https://astro.miya-lis.net/">
        {R.s @@ "→→→旧サイトはこちら←←←"}
      </a>
    </h3>
    <h1 className="text-4xl">
      {R.s @@ "※※※ THIS WEB SITE IS UNDER CONSTRUCTION ※※※"}
    </h1>
    <h2 className="text-3xl">
      <Link path="/"> {R.s @@ "→→作り途中のやつ←←"} </Link>
    </h2>
  </div>;
};