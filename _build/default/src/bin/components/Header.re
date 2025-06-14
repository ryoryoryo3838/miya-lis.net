[@react.component]
let make = () => {
  let route: string = ReasonReactRouter.useUrl().path |> String.concat("/");
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
      {R.s @@ "Index of /miya-lis/" ++ route}
    </h1>
  </header>;
};
