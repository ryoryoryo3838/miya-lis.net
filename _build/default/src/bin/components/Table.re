[@react.component]
let make = (~children) => {
  <div
    id="l-directory"
    className="pl-5 pr-5 max-lg:pl-[1.5vw] max-md:pl-0 max-lg:pr-[1.5vw] max-md:pr-0 text-2xl">
    <table
      id="l-directory>table"
      className="m-0 p-0 border-0 w-full  font-inherit align-middle border-collapse border-spacing-0 md:w-full md:max-w-md">
      <thead
        id="l-directory>table>thead"
        className="position-relative height-auto mb-4 max-lg:mb-[1.25vw] max-md:mv-[4vw] text-left font-sometype_mono">
        <tr>
          <th id="icon" />
          <th id="ttl" className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
            {R.s @@ "Name"}
          </th>
          <th
            id="update" className="pl-1.5 max-lg:pl-[.5vw] max-md:pl-[1.5vw]">
            {R.s @@ "Last Modified"}
          </th>
          <th id="size"> {R.s @@ "Size"} </th>
        </tr>
      </thead>
      <tbody
        id="l-directory>table>body"
        className="position-relative height-auto mb-4 max-lg:mb-[1.25vw] max-md:mv-[4vw] text-left font-sometype_mono pl-[5vw]">
        children
      </tbody>
    </table>
  </div>;
};

[@react.component]
let element = (~path, ~name /* , ~update, ~size */) => {
  <>
    <tr className="p-10 ">
      <th> {R.s @@ ""} </th>
      <th> <Link path> {R.s @@ name} </Link> </th>
      <th> {R.s @@ ""} </th>
      <th> {R.s @@ ""} </th>
    </tr>
  </>;
};
