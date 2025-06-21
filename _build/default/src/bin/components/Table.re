[@react.component]
let make = (~thead, ~tbody) => {
  <div
    id="l-directory"
    className="pl-5 pr-5 max-lg:pl-[1.5vw] max-md:pl-0 max-lg:pr-[1.5vw] max-md:pr-0 text-2xl">
    <table
      id="l-directory>table"
      className="m-0 p-0 border-0 w-full  font-inherit align-middle border-collapse border-spacing-0 md:w-full md:max-w-md">
      <thead
        id="l-directory>table>thead"
        className="position-relative height-auto mb-4 max-lg:mb-[1.25vw] max-md:mv-[4vw] text-left font-sometype_mono">
        thead
      </thead>
      <tbody
        id="l-directory>table>body"
        className="position-relative height-auto mb-4 max-lg:mb-[1.25vw] max-md:mv-[4vw] text-left font-sometype_mono pl-[5vw]">
        tbody
      </tbody>
    </table>
  </div>;
};

[@react.component]
let tbody = (~lst: list((string, list(string))), ~url=?) => {
  <>
    {lst
     |> List.map(((path, index)) =>
          <tr>
            {switch (index) {
             | [icon, ...other] =>
               let iconcomp =
                 <th>
                   <Link path>
                     <i
                       className={
                         "pr-[0.1vw] fa-xs text-center" ++ " " ++ icon
                       }
                     />
                   </Link>
                 </th>;
               let othercomp = {
                 other
                 |> List.map(x =>
                      switch (url, x) {
                      | (None, "-") =>
                        <th className="text-center">
                          <Link path> {R.s @@ x} </Link>
                        </th>
                      | (None, _) => <th> <Link path> {R.s @@ x} </Link> </th>
                      | (_, "-") =>
                        <th className="text-center">
                          <Link.url path> {R.s @@ x} </Link.url>
                        </th>
                      | (_, _) =>
                        <th> <Link.url path> {R.s @@ x} </Link.url> </th>
                      }
                    );
               };
               [iconcomp, ...othercomp] |> Array.of_list |> React.array;
             | [] => <div />
             }}
          </tr>
        )
     |> Array.of_list
     |> React.array}
  </>;
};

[@react.component]
let thead = (~index) => {
  <>
    <tr>
      {index
       |> List.map(x
            // <th id=x className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
            =>
              if (x == "Size") {
                <th id=x className="text-center"> {R.s @@ x} </th>;
              } else {
                <th id=x> {R.s @@ x} </th>;
              }
            )
       |> Array.of_list
       |> React.array}
    </tr>
    // <th id="icon" />
  </>;
};
