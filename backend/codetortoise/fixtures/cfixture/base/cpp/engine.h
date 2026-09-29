#ifndef CPP_ENGINE_H
#define CPP_ENGINE_H

struct Inner {
    int n;
};

struct State {
    Inner inner;
    int x;
};

namespace svc {

class Base {
public:
    virtual ~Base();
    virtual int base(State &s);
};

class Engine : public Base {
public:
    int step(State &st);
    int base(State &s) override;
    int level = 0;
};

}  // namespace svc

#endif
