[@react.component]
let make = () => {
  let route: string = ReasonReactRouter.useUrl().path |> String.concat("/");
  <>
    <header className="columns-2">
      <div className="mockup-window bg-base-200" />
      <div className="text-4xl text-bold font-serif">
        {R.s @@ "miya-lis.net/" ++ route}
      </div>
    </header>
  </>;
};
