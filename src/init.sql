-- eShop Advanced — Complete Database Setup (schema + 200 legislation)
-- Run: mysql -u root -proot < init.sql

CREATE DATABASE IF NOT EXISTS db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE db;

-- Drop in reverse dependency order
DROP TABLE IF EXISTS speeches;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS speakers;
DROP TABLE IF EXISTS legislation;

-- Student participants and their associated actions
CREATE TABLE speakers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(200) NOT NULL UNIQUE,
  password_hash VARCHAR(256) NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  school VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE speeches (
  id INT AUTO_INCREMENT PRIMARY KEY,
  speaker_id INT NOT NULL,
  total_time INT NOT NULL,
  affirmative BOOLEAN NOT NULL, -- True for affirmative, False for negation speech 
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_speaker_id FOREIGN KEY (speaker_id) REFERENCES speakers(id)
);

CREATE TABLE questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  speaker_id INT NOT NULL,
  speech_id INT NOT NULL, -- which speech was this question asked on
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_speaker_id FOREIGN KEY (speaker_id) REFERENCES speakers(id),
  CONSTRAINT fk_speech_id FOREIGN KEY (speech_id) REFERENCES speeches(id)
);

-- Legislation: bills, resolutions, etc.
CREATE TABLE legislation (
  id INT AUTO_INCREMENT PRIMARY KEY,
  school VARCHAR(100) NOT NULL,
  title VARCHAR(200) NOT NULL,
  body VARCHAR(3000),
  order INT NOT NULL, -- From [1 .. N]
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- Dummy legislation data
-- =====================================================================


INSERT INTO legislation (school, title, body, order) VALUES
-- Lincoln East 
('Lincoln East', 'Bill to Curb Eminent Domain', 'Establish more rigorous process before using eminent domain', 4),
('Lincoln East' , 'Resolution to GTFO Iraq', 'Basically lets leave Iraq, cuz we got enough probs at home', 2),

-- Millard North
('Millard North', 'Bill to Whatever', 'Do wtv, Idrc' 1),
('Millard North', 'Bill to Reduce Food Insecurity', 'Give a bajillion dollars to feed hungry ppl' 3),