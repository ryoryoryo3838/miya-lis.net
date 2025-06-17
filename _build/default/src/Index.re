module Error = {
  [@react.component]
  let make = () => {
    <div className="p-10 text-center">
      <h1 className="text-8xl items-center"> {R.s @@ "404 Not Found"} </h1>
      <p className="text-4xl pt-5">
        {R.s @@ "This is requested URL was not found on this server."}
      </p>
      <Link path="/">
        <p className="text-3xl pt-10"> {R.s @@ "Back to Home"} </p>
      </Link>
    </div>;
  };
};

module Router = {
  [@react.component]
  let make = () => {
    let route = ReasonReactRouter.useUrl();
    switch (route.path) {
    | [] => <Home />
    | ["aboutme"] => <AboutMe.detail />
    | ["prev"] => <Home.prev />
    | ["mutual"] => <MutalLink />
    | ["aquarium"] => <Aquarium />
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
