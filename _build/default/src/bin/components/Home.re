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
    // <DirListing />
    <h1 className="text-4xl">
      {R.s @@ {j|※※※ THIS WEB SITE IS UNDER CONSTRUCTION ※※※|j}}
    </h1>
  </div>;
};
