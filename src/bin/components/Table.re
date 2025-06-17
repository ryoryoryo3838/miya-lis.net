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
let tbody = (~lst: list((string, list(string)))) => {
  <>
    {lst
     |> List.map(((path, index)) =>
          <tr>
            {index
             |> List.map(x => <th> <Link path> {R.s @@ x} </Link> </th>)
             |> Array.of_list
             |> React.array}
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
      <th id="icon" />
      {index
       |> List.map(x => {
            <th id=x className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
              {R.s @@ x}
            </th>
          })
       |> Array.of_list
       |> React.array}
    </tr>
  </>;
};
