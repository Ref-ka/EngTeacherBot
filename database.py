import sqlite3 as lite


class DataBase:
    def __init__(self):
        self.conn = lite.connect("EngTeacher.db", check_same_thread=False)
        self.conn.execute('pragma foreign_keys = on')
        self.conn.commit()
        self.cur = self.conn.cursor()

    def query(self, arg, values=None):
        if not values:
            self.cur.execute(arg)
        else:
            self.cur.execute(arg, values)
        self.conn.commit()

    def fetchone(self, arg, values=None):
        if not values:
            self.cur.execute(arg)
        else:
            self.cur.execute(arg, values)
        return self.cur.fetchone()

    def fetchall(self, arg, values=None):
        if not values:
            self.cur.execute(arg)
        else:
            self.cur.execute(arg, values)
        return self.cur.fetchall()

    def input_words(self, chat_id, eng_name, ru_name):
        self.cur.execute(f"INSERT INTO words VALUES ((?), (?), (?), (?))", (chat_id, eng_name, ru_name, None))
        self.conn.commit()

    def output_words(self, chat_id):
        print(type(chat_id))
        return self.fetchall(f"SELECT eng_word, ru_word FROM words WHERE chat_id == (?)", [chat_id])

    def delete_words(self, chat_id: int, word: str):
        print(chat_id, word)
        self.cur.execute(f"DELETE FROM words WHERE chat_id == (?) AND eng_word == (?)", (chat_id, word))
        self.conn.commit()
        print('deleted!')

    def change_word(self, chat_id: int, words: dict):
        if words["lang"] == 'en':
            self.cur.execute("UPDATE words SET eng_word = (?) WHERE chat_id == (?) AND eng_word == (?)",
                             [words['changed'], chat_id, words['changeable']])
        else:
            self.cur.execute("UPDATE words SET ru_word = (?) WHERE chat_id == (?) AND eng_word == (?)",
                             [words['changed'], chat_id, words['changeable']])
        self.conn.commit()

    def __del__(self):
        self.conn.close()
