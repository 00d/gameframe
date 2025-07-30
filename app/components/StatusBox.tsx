import React from "react";
//import styles from './StatusBox.module.css';

interface User {
  id: number;
  name: string;
}

const StatusBox = async () => {
  const response = await fetch("https://jsonplaceholder.typicode.com/users");
  const users: User[] = await response.json();

  return (
    <div  className='p-4 bg-blue-700 text-white border-4 border-white rounded-lg shadow-sm'>
        <h2>Status Box</h2>
        <ul>
          {users.map((user) => (
            <li key={user.id}>{user.name}</li>
          ))}
        </ul>
    </div>
  );
};

export default StatusBox;
