#include "cpp/engine.h"

namespace svc {

Base::~Base() {}

int Base::base(State &s)
{
    return s.x;
}

int Engine::base(State &s)
{
    s.x = 1;
    return 1;
}

int Engine::step(State &st)
{
    auto &r = st.inner;
    r.n += 3;
    level = 3;
    return base(st) + 1;
}

}  // namespace svc
