type table = list((string, string));
let showList = (tbl: table, ~cN: string) => {
  tbl
  |> List.map(((path, name)) =>
       <li className=cN> <a href=path> {R.s @@ name} </a> </li>
     )
  |> Array.of_list
  |> React.array;
};

let title = (title: string) => {
  <h1 className="text-5xl m-5"> {R.s @@ title} </h1>;
};
