[@react.component]
let make = () => {
  let year = Js.Date.make()->Js.Date.getFullYear->int_of_float->string_of_int;
  <>
    <footer className="text-center fixed bottom-0 w-full">
      {R.s @@ "©" ++ year ++ " miya. All rights reserved."}
    </footer>
  </>;
};
