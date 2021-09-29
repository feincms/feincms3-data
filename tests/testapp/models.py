from django.db import models


class Parent(models.Model):
    name = models.CharField(default="name", max_length=20)


class Child(models.Model):
    name = models.CharField(default="name", max_length=20)

    class Meta:
        abstract = True


class Child1(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)


class Child2(Child):
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
