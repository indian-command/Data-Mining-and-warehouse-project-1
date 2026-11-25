CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- F1: Accounts & Profiles
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('student', 'faculty', 'researcher', 'admin')),
    department VARCHAR(100) NOT NULL,
    bio TEXT,
    interest_tags TEXT[] DEFAULT '{}',
    profile_url TEXT,
    interest_embedding vector(384),
    is_flagged_spam BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_follows (
    follower_id UUID REFERENCES users(id) ON DELETE CASCADE,
    following_id UUID REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (follower_id, following_id)
);

CREATE TABLE topic_follows (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic_tag VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, topic_tag)
);

-- F3 & F4: Canonical Papers & External Articles (Deduplicated)
CREATE TABLE papers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_doi VARCHAR(255) UNIQUE,
    arxiv_id VARCHAR(100) UNIQUE,
    openalex_id VARCHAR(100) UNIQUE,
    title TEXT NOT NULL,
    authors TEXT[] NOT NULL,
    abstract TEXT,
    published_year INT,
    venue VARCHAR(255),
    url TEXT,
    sources TEXT[] DEFAULT '{}',          -- e.g. {'openalex', 'arxiv', 'semantic_scholar'}
    pagerank_score DOUBLE PRECISION DEFAULT 0.0,
    save_count INT DEFAULT 0,
    search_tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, ''))
    ) STORED,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_papers_tsv ON papers USING GIN (search_tsv);
CREATE INDEX idx_papers_embedding ON papers USING hnsw (embedding vector_cosine_ops);

-- Citation Graph Edges (for F5 PageRank)
CREATE TABLE paper_citations (
    citing_paper_id UUID REFERENCES papers(id) ON DELETE CASCADE,
    cited_paper_id UUID REFERENCES papers(id) ON DELETE CASCADE,
    PRIMARY KEY (citing_paper_id, cited_paper_id)
);

-- F8: Paper Text Chunks for RAG Research Assistant
CREATE TABLE paper_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    paper_id UUID REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384)
);

CREATE INDEX idx_chunks_embedding ON paper_chunks USING hnsw (embedding vector_cosine_ops);

-- F3: Personal Collections & Shared Chanakya Library Saves
CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE library_saves (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    paper_id UUID REFERENCES papers(id) ON DELETE CASCADE,
    collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
    private_notes TEXT,
    saved_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, paper_id)
);

-- F2: Posts, Discussions & Upvotes
CREATE TABLE posts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    author_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    attached_paper_id UUID REFERENCES papers(id) ON DELETE SET NULL,
    attached_url TEXT,
    upvote_count INT DEFAULT 0,
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    parent_comment_id UUID REFERENCES comments(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE post_upvotes (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    post_id UUID REFERENCES posts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id)
);

-- Event Log (feeds DuckDB Parquet ETL for F7 Trends & F9 Admin Analytics)
CREATE TABLE activity_events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(40) NOT NULL,      -- 'search', 'view_paper', 'save_paper', 'create_post', 'comment'
    target_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);