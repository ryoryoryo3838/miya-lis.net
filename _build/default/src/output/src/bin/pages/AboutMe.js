// Generated by Melange

import * as Link from "../components/Link.js";
import * as R from "../../lib/r/R.js";
import * as Stdlib__Array from "melange/array.js";
import * as Stdlib__List from "melange/list.js";
import * as JsxRuntime from "react/jsx-runtime";

function element(category, lst) {
  return JsxRuntime.jsxs(JsxRuntime.Fragment, {
    children: [
      JsxRuntime.jsx("p", {
        children: R.s(category)
      }),
      JsxRuntime.jsx("ul", {
        children: Stdlib__Array.of_list(Stdlib__List.map((function (x) {
          return JsxRuntime.jsx("li", {
            children: R.s(x)
          });
        }), lst)),
        className: "pl-15"
      })
    ]
  });
}

function AboutMe$home(Props) {
  return JsxRuntime.jsxs("div", {
    children: [
      JsxRuntime.jsxs("div", {
        children: [
          JsxRuntime.jsx("h3", {
            children: R.s("Name: miya"),
            className: "text-3xl"
          }),
          JsxRuntime.jsx("h3", {
            children: R.s("Affiliation: KLiS'23"),
            className: "text-3xl"
          }),
          JsxRuntime.jsx("h3", {
            children: JsxRuntime.jsx(Link.make, {
              path: "/aboutme",
              children: R.s("(for more detail, see \"About me\")")
            }),
            className: "text-2xl"
          })
        ],
        className: "flex-col pr-0"
      }),
      JsxRuntime.jsx("img", {
        className: "ml-0 w-[150px]",
        alt: "icon",
        src: "/icon.svg"
      })
    ],
    className: "font-serif flex flex-row justify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold items-center lg:pr-[50vw]",
    id: "title"
  });
}

function AboutMe$detail(Props) {
  return JsxRuntime.jsxs("div", {
    children: [
      JsxRuntime.jsx("h2", {
        children: R.s("About me"),
        className: "text-5xl"
      }),
      JsxRuntime.jsx("h3", {
        children: R.s("氏名: 清宮亮太郎"),
        className: "text-3xl"
      }),
      JsxRuntime.jsxs("h3", {
        children: [
          element("所属: ", {
            hd: "筑波大学",
            tl: {
              hd: "情報学群",
              tl: {
                hd: "知識情報・図書館学類",
                tl: {
                  hd: "知識科学主専攻",
                  tl: {
                    hd: "横山研究室",
                    tl: {
                      hd: "",
                      tl: /* [] */ 0
                    }
                  }
                }
              }
            }
          }),
          element("分野: ", {
            hd: "#専攻",
            tl: {
              hd: "図書館情報学(全体の理論や情報概念について)",
              tl: {
                hd: "哲学(LIS-PhilとPI周辺)",
                tl: {
                  hd: "#興味遍歴",
                  tl: {
                    hd: "分析哲学",
                    tl: {
                      hd: "情報思想",
                      tl: {
                        hd: "システム論",
                        tl: {
                          hd: "強化学習",
                          tl: {
                            hd: "etc...",
                            tl: /* [] */ 0
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }),
          element("言語: ", {
            hd: "日本語: 母語",
            tl: {
              hd: "英語: CEFR B1程度",
              tl: /* [] */ 0
            }
          }),
          element("プログラミング言語: ", {
            hd: "#ちょっとわかる:",
            tl: {
              hd: "Python",
              tl: {
                hd: "OCaml",
                tl: {
                  hd: "Reason",
                  tl: {
                    hd: "Elm",
                    tl: {
                      hd: "#気になる:",
                      tl: {
                        hd: "HTML/CSS",
                        tl: {
                          hd: "TypeScript",
                          tl: {
                            hd: "C",
                            tl: /* [] */ 0
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          })
        ],
        className: "text-2xl"
      })
    ],
    className: "font-serif jstify-between box-border  pt-5 pb-5 pl-4 pr-4 leading-normal font-bold"
  });
}

const home = AboutMe$home;

const detail = AboutMe$detail;

export {
  element,
  home,
  detail,
}
/* Link Not a pure module */
