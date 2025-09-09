let table = () => {
  <Table
    thead={<Table.thead index=["", "Name", "Last modified", "Size"] />}
    tbody=
      {<>
         <Table.tbody
           lst=[
             (
               "/aboutme",
               ["fa-solid fa-address-card", "About me", "2025-06-17", "-"],
             ),
             (
               "/prev",
               ["fa-solid fa-rotate", "Prev site", "2025-06-17", "-"],
             ),
             (
               "/mutual",
               ["fa-solid fa-link", "Mutual link", "2025-06-17", "-"],
             ),
             (
               "/aquarium",
               ["fa-solid fa-fish", "Aquarium", "2025-06-18", "-"],
             ),
           ]
         />
         <Table.tbody
           lst=[
             (
               "https://blog.miya-lis.net",
               ["fa-solid fa-book", "Blog", "2025-06-18", "-"],
             ),
           ]
           url="url"
         />
       </>}
  />;
};

// ホーム
[@react.component]
let make = () => {
  <>
    <Layout.wrap>
      <Header />
      <Layout.wrapMain> <AboutMe.home /> {table()} </Layout.wrapMain>
    </Layout.wrap>
    <Footer />
  </>;
};

