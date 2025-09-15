///
/// Router
///
module Router = {
  [@react.component]
  let make = () => {
    let route = ReasonReactRouter.useUrl();
    Js.log(route.path);
    switch (route.path) {
    | [] => <Exp />
    | ["home"]
    | ["index"] => <Home />
    | ["aboutme"] => <Post path="aboutme" />
    | ["post", path, ..._] => <Post path />
    | _ =>
      Js.log(route.path);
      <Home />;
    };
  };
};

///
/// Render
///
let node = ReactDOM.querySelector("#root");
switch (node) {
| None =>
  Js.Console.error("Failed to start React: couldn't find the #root element")
| Some(root) =>
  let root = ReactDOM.Client.createRoot(root);
  ReactDOM.Client.render(root, <Router />);
};
