[@react.component]
let make = () => {
  <header
    id="l-title"
    className="flex flex-wrap items-center justify-between box-border mb-6 pl-5 pr-5 pt-0 max-md:pt-[4vw] max-lg:mb-[2vw] max-md:mb-[4.5vw] max-lg:pt-[3vw] max-lg:pl-[1.5vw] max-lg:pr-[1.5vw]md:w-full md:max-w-screen-md">
    <h2
      id="l-title>h2"
      className="leading-normal font-bold text-4xl max-lg:text-[3vw] max-md:text-[4.5vw] w-4/5 font-serif
          ">
      {R.s @@ "Name: Ryotaro Seimiya"}
      <br />
      {R.s @@ "Affiliation: KLiS'23"}
    </h2>
  </header>;
};
