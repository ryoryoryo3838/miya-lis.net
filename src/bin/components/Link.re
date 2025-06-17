[@react.component]
let make = (~path, ~children) => {
  <a
    href=path
    onClick={e => {
      React.Event.Mouse.preventDefault(e);
      ReasonReactRouter.push(path);
    }}>
    children
  </a>;
};

[@react.component]
let url = (~path, ~children) => {
  <a href=path> children </a>;
};
