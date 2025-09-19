[@react.component]
let make = (~children: React.element) => {
  <div className="noise"> <Header /> children <Footer /> </div>;
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
