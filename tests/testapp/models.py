from django.db import models


class Parent(models.Model):
    pass


class Child(models.Model):
    class Meta:
        abstract = True


class Child1(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)


class Child2(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
