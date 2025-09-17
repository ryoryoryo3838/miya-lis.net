[@react.component]
let make = () => {
  let route: string = ReasonReactRouter.useUrl().path |> String.concat("/");
  <>
    <header className="text-right mr-10">
      <div className="columns-2 flex m-3">
        <h1 className="text-6xl mr-auto text-left m-5">
          {R.s @@ "miya-lis.net/" ++ route}
        </h1>
        <img
          src="/icon.svg"
          alt="icon"
          className="ml-auto max:ml-[25%] w-[96px] h-[96px] mr-10"
        />
      </div>
    </header>
  </>;
};
