[@react.component]
let make = () => {
  <>
    {Util.title("さかなです")}
    <div className="text-2xl m-5 mt-10">
      {R.s @@ "そのうち魚を泳がせます（未定）"}
    </div>
  </>;
};
