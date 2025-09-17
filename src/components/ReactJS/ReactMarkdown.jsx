import React from 'react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import '../../index.css'
const md = `

`
const modules = import.meta.glob("/static/post/*.md", {
  eager: true,
  query: '?raw',
  });


export default function MarkdownJS({path}) {
  path = ("/static/post/" + path + ".md")
  console.log("path: ", path)
  console.log("modules: ",  modules)
  console.log("modules[path]: ", modules[path])
  console.log("modules[path][default]: ", modules[path]["default"])
  const md = modules[path]["default"]
  return ( 
    <div className='markdown prose'>
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
    </div>
  )
}
