let table = () => {
  <div>
    <Table
      thead={<Table.thead index=["Name", "Link", "Size"] />}
      tbody={
        <Table.tbody
          lst=[
            (
              "https:かすしゅく.みんな/",
              ["", "-", "かすしゅく.みんな", "-"],
            ),
            (
              "https://romablog-lime.vercel.app/about",
              ["", "Romanohu", "Roma.Log(/\t・\t・\t)/", "-"],
            ),
            (
              "https://mikazukimo.github.io/zukimo_shiroko_suki/",
              ["", "Zukimo", "ずきもの書庫", "-"],
            ),
            ("https://utsugi0101.dev/", ["", "Ustugi", "Ustugi0101", "-"]),
          ]
          url="url"
        />
      }
    />
  </div>;
};

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
