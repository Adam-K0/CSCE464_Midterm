-- Congressional Debate — Presiding Officer Helper
-- Run: mysql -u root < init.sql

CREATE DATABASE IF NOT EXISTS congress_debate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE congress_debate;

-- Drop in reverse dependency order
DROP TABLE IF EXISTS question_queue;
DROP TABLE IF EXISTS speech_queue;
DROP TABLE IF EXISTS speeches;
DROP TABLE IF EXISTS session_state;
DROP TABLE IF EXISTS legislation;
DROP TABLE IF EXISTS speakers;

-- =====================================================================
-- Student speakers
-- =====================================================================
CREATE TABLE speakers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(200) NOT NULL UNIQUE,
  password_hash VARCHAR(256) NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  school VARCHAR(100) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- Legislation docket
-- =====================================================================
CREATE TABLE legislation (
  id INT AUTO_INCREMENT PRIMARY KEY,
  school VARCHAR(100) NOT NULL,
  title VARCHAR(200) NOT NULL,
  body TEXT,
  leg_order INT NOT NULL,
  status ENUM('pending', 'active', 'completed') NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- Session state — singleton row tracks current debate state
-- =====================================================================
CREATE TABLE session_state (
  id INT PRIMARY KEY DEFAULT 1,
  active_legislation_id INT DEFAULT NULL,
  current_speech_id INT DEFAULT NULL,
  phase ENUM('idle', 'speech_queue', 'speech_in_progress', 'questioning') NOT NULL DEFAULT 'idle'
);
INSERT INTO session_state (id) VALUES (1);

-- =====================================================================
-- Record of all speeches given during the round
-- =====================================================================
CREATE TABLE speeches (
  id INT AUTO_INCREMENT PRIMARY KEY,
  legislation_id INT NOT NULL,
  speaker_id INT NOT NULL,
  is_affirmative BOOLEAN NOT NULL,
  speech_type ENUM('authorship', 'first_negative', 'regular') NOT NULL DEFAULT 'regular',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (legislation_id) REFERENCES legislation(id),
  FOREIGN KEY (speaker_id) REFERENCES speakers(id)
);

-- Add FK now that speeches table exists
ALTER TABLE session_state
  ADD CONSTRAINT fk_ss_leg FOREIGN KEY (active_legislation_id) REFERENCES legislation(id),
  ADD CONSTRAINT fk_ss_speech FOREIGN KEY (current_speech_id) REFERENCES speeches(id);

-- =====================================================================
-- Speech queue — speakers requesting to speak on current leg
-- =====================================================================
CREATE TABLE speech_queue (
  id INT AUTO_INCREMENT PRIMARY KEY,
  legislation_id INT NOT NULL,
  speaker_id INT NOT NULL,
  is_affirmative BOOLEAN NOT NULL,
  status ENUM('waiting', 'speaking', 'done', 'cancelled') NOT NULL DEFAULT 'waiting',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (legislation_id) REFERENCES legislation(id),
  FOREIGN KEY (speaker_id) REFERENCES speakers(id)
);

-- =====================================================================
-- Question queue — speakers requesting to question after a speech
-- =====================================================================
CREATE TABLE question_queue (
  id INT AUTO_INCREMENT PRIMARY KEY,
  speech_id INT NOT NULL,
  speaker_id INT NOT NULL,
  status ENUM('waiting', 'asking', 'done', 'cancelled') NOT NULL DEFAULT 'waiting',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (speech_id) REFERENCES speeches(id),
  FOREIGN KEY (speaker_id) REFERENCES speakers(id)
);

-- =====================================================================
-- Sample legislation
-- =====================================================================
INSERT INTO legislation (school, title, body, leg_order) VALUES
('Lincoln East', 'A Bill to Curb Eminent Domain Abuse', 'Be it enacted by this Congress that stricter criteria and due process protections be established before any government entity may exercise eminent domain over private property.', 1),
('Lincoln East', 'A Resolution to Withdraw Troops from Overseas Conflicts', 'Be it resolved that the United States should prioritize domestic investment by withdrawing military forces from prolonged overseas engagements.', 2),
('Millard North', 'A Bill to Expand Broadband Access', 'Be it enacted that federal funding be allocated to expand high-speed internet infrastructure to underserved rural and urban communities.', 3),
('Millard North', 'A Bill to Reduce Food Insecurity', 'Be it enacted that additional federal resources be directed toward food assistance programs to combat hunger in low-income communities.', 4);