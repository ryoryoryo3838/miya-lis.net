[@react.component]
let make = (~path: string): React.element => {
  Js.log(path);
  //<Layout>
  <div className="z-50 font-serif"> <Makrdown path /> </div>;
  //</Layout>;
};
