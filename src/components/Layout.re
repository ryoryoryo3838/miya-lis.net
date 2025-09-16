[@react.component]
let make = (~children: React.element) => {
  <> <Header /> children <Footer /> </>;
};
[@react.component]
let make_bak = (~children: React.element) => {
  <>
    <Header />
    <BackGround.grid>
      <div className="grid place-content-center"> children </div>
    </BackGround.grid>
    <Footer />
  </>;
};
