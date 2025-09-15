let gridStyle =
  R.style(
    ~background=
      "linear-gradient(to right, #e2e8f0 1px, transparent 1px),linear-gradient(to bottom, #e2e8f0 1px, transparent 1px)",
    ~backgroundSize="20px 30px",
    ~maskImage=
      "radial-gradient(ellipse 70% 60% at 50% 100%, #000 60%, transparent 100%)",
    (),
  );
[@react.component]
let grid = (~children) => {
  <div className="min-h-screen w-full bg-[#f8fafc] relative">
    <div className="absolute inset-0 z-0" style=gridStyle />
    children
  </div>;
};

let backStyle =
  R.style(
    ~background=
      "radial-gradient(125% 125% at 50% 10%, #fff 40%, #6366f1 100%)",
    (),
  );
[@react.component]
let back = (~children) => {
  <>
    <div className="min-h-screen w-full relative">
      <div className="absolute inset-0 z-0" style=backStyle> children </div>
    </div>
  </>;
};
