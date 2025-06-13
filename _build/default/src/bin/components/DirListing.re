[@react.component]
let make = () => {
  <>
    <table>
      <thead>
        <tr>
          <th />
          <th> {R.s @@ "Name"} </th>
          <th> {R.s @@ "Last Modified"} </th>
          <th> {R.s @@ "Size"} </th>
          <th> {R.s @@ "Description"} </th>
        </tr>
      </thead>
    </table>
  </>;
};
