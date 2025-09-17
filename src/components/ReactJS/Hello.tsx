import { useState } from "react";

interface Data {
  output: string;
}

function Hello() {
  const [output, setOutput] = useState<string>("");

  const send = async () => {
    const response = await fetch("/helloworld", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });

  const data: Data = await response.json();
  setOutput(data.output);
  }
  return (
    <>
      <button onClick={send}>送信</button>
      <p>{output}</p>
    </>
  )
}

export default Hello

