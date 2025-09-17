import React, { useState } from 'react';

function UserForm() {
  const [sql, setSql] = useState('');
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
        body: JSON.stringify({ sql: username }),
      });

      const data = await res.json();
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
          value={sql}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="ユーザー名を入力"
        />
        <button type="submit" disabled={loading}>
          {loading ? '送信中...' : 'ユーザーを作成'}
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
