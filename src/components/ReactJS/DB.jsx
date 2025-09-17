import React, { useState } from 'react';

function UserForm() {
  const [text, setText] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault(); // フォームのデフォルトの送信動作を防止
    setLoading(true);

    try {
      const res = await fetch('/api/db', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({txt: text}),
      });

      const data = await res.json();
      console.log(data.message);
      console.log(data.executeSql);
      setResponse(data);

    } catch (error) {
      console.error("API呼び出しエラー:", error);
      setResponse({ error: "API呼び出しに失敗しました。" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="追加したいテキストを入力"
        />
        <button type="submit" disabled={loading}>
          {loading ? '送信中...' : 'テキストを追加'}
        </button>
      </form>
      {response && (
        <pre>
          {JSON.stringify(response, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default UserForm;
