[@react.component]
let wrap = (~children) => {
  <div
    id="Wrap"
    className="
  text-[#333]
  text-xl max-lg:text-[1.5vw] max-md:text-[3.5vw] text-[62.5%] font-normal backface-hidden palt
  max-lg:pl-
  ">
    children
  </div>;
};

[@react.component]
let wrapMain = (~children) => {
  <div
    id="Wrap Main"
    className="
      pb-20 max-lg:pb-[6vw] max-md:pb-[14vw]
      ">
    children
  </div>;
};
