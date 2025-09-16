[@react.component]
let make = () => {
  let route: string = ReasonReactRouter.useUrl().path |> String.concat("/");
  <>
    <header className="text-right mr-10">
      <div className="text-3xl  font-semibold font-serif mb-10">
        {R.s @@ "miya-lis.net/" ++ route}
      </div>
    </header>
  </>;
};
