module Hello = {
  [@react.component]
  let make = () => {
    <h1> {React.string("ReasonReact + Melange + Vite!!!")} </h1>
  }
};

module Error = {
  [@react.component]
  let make = () => {
    <h1>{ React.string("Error!!!")}</h1>
  }
};

module App = {
  [@react.component]
  let make = () => {
    let route = ReasonReactRouter.useUrl();
    switch (route.path) {
    | ["index", ..._] => <Hello />
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
  ReactDOM.Client.render(root, <App />);
};
