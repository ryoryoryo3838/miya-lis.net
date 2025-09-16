///
/// Router
///
let router = (path: list(string)): React.element => {
  switch (path) {
  | [] => <Home />
  | ["home"]
  | ["index"] => <Home />
  | _ =>
    <Layout>
      {switch (path) {
       | ["bookshelf"] => <BookShelf />
       | ["link"] => <Link />
       | ["aqualium"] => <Sakana />
       | ["misc"] => <MISC />
       | ["aboutme"] => <Post path="aboutme" />
       | ["post", path, ..._] => <Post path />
       | _ => <Home />
       }}
    </Layout>
  };
};
module Router = {
  [@react.component]
  let make = () => {
    let route = ReasonReactRouter.useUrl();
    <> {router(route.path)} </>;
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
