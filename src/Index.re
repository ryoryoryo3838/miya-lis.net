module Index = {
  [@react.component]
  let make = () => {
    <h1> {R.s @@ "ReasonReact + Melange + Vite!!!"} </h1>;
  };
};

module Error = {
  [@react.component]
  let make = () => {
    <h1> {React.string("Error!!!")} </h1>;
  };
};

module Router = {
  [@react.component]
  let make = () => {
    let route = ReasonReactRouter.useUrl();
    switch (route.path) {
    | [] => <Index />
    | _ => <Error />
    };
  };
};

let node = ReactDOM.querySelector("#root");
switch (node) {
| None =>
  Js.Console.error("Failed to start React: couldn't find the #root element")
| Some(root) =>
  let root = ReactDOM.Client.createRoot(root);
  ReactDOM.Client.render(root, <Router />);
};
