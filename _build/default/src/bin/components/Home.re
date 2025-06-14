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

[@react.component]
let dev = () => {
  <div
    id="Wrap"
    className="
  text-[#333]
  text-xl max-lg:text-[1.5vw] max-md:text-[3.5vw]
  ">
    <header
      id="Head l-header"
      className="
        pt-8 pl-5 pr-5
        max-lg:pt-[2.5vw] max-md:pt-[10vw]
        max-lg:pl-[1.5vw]
        max-lg:pr-[1.5vw]
        ">
      <h1
        id="l-header>h1"
        className="
        m-0 p-0 font-bold text-6xl
        max-lg:text-[4.5vw] max-md:text-[10vw]
        max-md:leading-tight
        font-serif
        ">
        {R.s @@ "Index of /mofumofu/"}
      </h1>
    </header>
    <div
      id="Wrap Main"
      className="
      pb-20 max-lg:pb-[6vw] max-md:pb-[14vw]
      ">
      <header
        id="l-title"
        className="flex flex-wrap items-center justify-between box-border mb-6 pl-5 pr-5 p5-5max-lg:mb-[2vw] max-md:mb-[4.5vw] max-lg:pt-[3vw] max-lg:pl-[1.5vw] max-lg:pr-[1.5vw]md:w-full md:max-w-screen-md">
        <h2
          id="l-title>h2"
          className="leading-normal font-bold text-4xl max-lg:text-[3vw] max-md:text-[4.5vw] w-4/5 font-serif
          ">
          {R.s @@ "Yuka Nagase"}
          <br />
          {R.s @@ "Mofu Mofu Project"}
        </h2>
        <div
          id="l-directory"
          className="pl-5 pr-5 max-lg:pl-[1.5vw] max-md:pl-0 max-lg:pr-[1.5vw] max-md:pr-0 ">
          <table
            id="l-directory>table"
            className="m-0 p-0 border-0 w-full text-[100%] font-inherit align-middle border-collapse border-spacing-0 md:w-full md:max-w-md ">
            <thead
              id="l-directory>table>thead"
              className="position-relative height-auto mb-4 text-xl max-lg:mb-[1.25vw] max-md:mv-[4vw] text-left font-sometype_mono">
              <tr>
                <th id="icon" />
                <th
                  id="ttl"
                  className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
                  {R.s @@ "Name"}
                </th>
                <th
                  id="update"
                  className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
                  {R.s @@ "Last Modified"}
                </th>
                <th id="size"> {R.s @@ "Size"} </th>
              </tr>
            </thead>
          </table>
        </div>
      </header>
    </div>
  </div>;
};
